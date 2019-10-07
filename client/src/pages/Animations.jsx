import React from "react";
import I18n from "i18n-js";
import "./Animations.css";
import Period from "../components/Period";
import moment from "moment";
import {allowedAggregatedScales, getPeriod} from "../utils/Time";
import "moment/locale/nl";
import Filters from "../components/Filters";
import {loginAggregated, loginTops} from "../api";
import FlipMove from "react-flip-move";
import {isEmpty} from "../utils/Utils";

moment.locale(I18n.locale);

let name = "sp_entity_id";
const value = "count_user_id";
const offsetName = 335;
const maxDisplay = 15;
const local = false;

export default class Animations extends React.PureComponent {

    constructor(props) {
        super(props);
        this.state = {
            data: [],
            tempData: [],
            colors: {},
            provider: "sp",
            state: "prodaccepted",
            from: moment().add(-5, "year").startOf("year"),
            to: moment().endOf("day"),
            scale: "year",
            initial: true,
            animationDuration: 1350,
            refreshDuration: 5750,
            largestValue: 0
        };
        this.flipContainer = React.createRef();
    }

    getOldValue = (data, key, fallback) => {
        const val = data.find(d => d[name] === key);
        if (isEmpty(val)) {
            return fallback;
        }
        return val[value];
    };

    refresh = (initial = true) => {
        const {colors, from, scale, provider, data, refreshDuration, state} = this.state;
        if (!this.interval && initial) {
            this.interval = setInterval(() =>
                this.refresh(false), refreshDuration);
        }
        let newFrom = initial ? from : moment(from).add(1, scale);
        if (newFrom.isAfter(moment())) {
            newFrom = from;
            clearInterval(this.interval);
            this.interval = undefined;
            return;
        }
        const period = getPeriod(newFrom, scale);
        const groupBy = provider === "sp" ? "sp_id" : "idp_id";
        const promise = local ? loginTops : loginAggregated;
        promise({
            period: period,
            include_unique: false,
            group_by: groupBy,
            state: state
        }).then(res => {
            if (res.length === 1 && res[0] === "no_results") {
                this.setState({data: [], from: newFrom});
            } else {
                const sorted = res.sort((a, b) => b[value] - a[value]).slice(0, maxDisplay);
                sorted.forEach(item => {
                    if (!colors[item[name]]) {
                        colors[item[name]] = "#" + (0x1000000 + (Math.random()) * 0xffffff).toString(16).substr(1, 6); //"#a8d9e6";
                    }
                });
                const tempData = sorted.map(item => ({
                    [name]: item[name],
                    [value]: this.getOldValue(data, item[name], item[value])
                }));
                this.setState({
                    data: tempData,
                    tempData: sorted,
                    colors: colors,
                    from: newFrom,
                    largestValue: res.reduce((acc, curr) => Math.max(acc, curr[value]), 0)
                });
            }
        });
    };

    componentDidMount() {
        this.interval = setInterval(() => this.refresh(false), this.state.refreshDuration);
        const offsetWidth = this.flipContainer.current.offsetWidth;
        this.setState({offsetWidth});
        this.refresh();
    }

    getLeftHandFilters = (to, from, scale, provider, state) =>
        <section className="container">
            <Period onChangeFrom={this.changeAttr("from")}
                    onChangeTo={() => true}
                    onChangeScale={this.changeAttr("scale")}
                    to={to}
                    from={from}
                    scale={scale}
                    aggregate={true}
                    allowedScales={allowedAggregatedScales.slice(0, 4)}
                    disabled={[]}/>
            <Filters displayProvider={true}
                     onChangeProvider={this.changeAttr("provider")}
                     provider={provider}
                     onChangeState={this.changeAttr("state")}
                     state={state}
                     displayUniques={false}
            />
        </section>;


    componentWillUnmount = () => clearInterval(this.interval);

    changeAttr = attrName => val => {
        clearInterval(this.interval);
        this.interval = undefined;
        if (attrName === "provider") {
            name = val === "sp" ? "sp_entity_id" : "idp_entity_id";
        }
        this.setState({[attrName]: val}, this.refresh);
    };

    onStartAnimation = () => {
        setTimeout(() => requestAnimationFrame(() => {
            const {tempData} = this.state;
            this.setState({data: tempData, tempData: []})
        }), this.state.animationDuration + 650);
    };

    getName = name => {
        const dictRef = this.state.provider === "sp" ? this.props.serviceProvidersDict : this.props.identityProvidersDict;
        const provider = dictRef[name] || {};
        return provider.name_en || name;
    };

    getWidth = (largestValue, offsetWidth, value) => {
        return `${((value / largestValue) * (offsetWidth - offsetName - 15)) + offsetName}px`;
    };

    render() {
        const {data, colors, provider, state, from, to, scale, animationDuration, largestValue, offsetWidth} = this.state;
        return (
            <div className="animations">
                {this.getLeftHandFilters(to, from, scale, provider, state)}
                <section className="content" ref={this.flipContainer}>

                    <p className="title">{I18n.t("live.aggregatedChartTitlePeriod", {
                        period: getPeriod(from, scale),
                        group: I18n.t(`chart.${provider}`),
                        institutionType: ""
                    })}</p>

                    <FlipMove duration={animationDuration} onFinishAll={this.onFinishAnimation}
                              className="flip-wrapper" onStartAll={this.onStartAnimation}
                              appearAnimation={false} enterAnimation={false} leaveAnimation={false}>
                        {data.map((item, i) =>
                            <div key={item[name]} className="row" style={{
                                width: this.getWidth(largestValue, offsetWidth, item[value]),
                                backgroundColor: colors[item[name]]
                            }}>
                                <p>{this.getName(item[name])}</p>
                                <span className="value">{item[value]}</span>
                            </div>)}
                    </FlipMove>
                    {data.length === 0 && <p>{I18n.t("chart.noResults")}</p>}
                </section>
            </div>
        );
    }

}